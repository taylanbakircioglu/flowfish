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
  Table,
  Tooltip,
  theme,
  Segmented,
  Badge
} from 'antd';
import { 
  ApiOutlined,
  GlobalOutlined,
  SwapOutlined,
  CloudServerOutlined,
  LockOutlined,
  ThunderboltOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  LinkOutlined,
  NodeIndexOutlined,
  RadarChartOutlined,
  HeatMapOutlined,
  FireOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  AlertOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useGetCommunicationStatsQuery, useGetCommunicationsQuery, useGetCrossNamespaceCommunicationsQuery, useGetHighRiskCommunicationsQuery, useGetErrorStatsQuery } from '../../../store/api/communicationApi';
import { useGetDnsQueriesQuery, useGetSniEventsQuery, useGetNetworkFlowsQuery } from '../../../store/api/eventsApi';
import { useTheme } from '../../../contexts/ThemeContext';

// Import custom components
import AnimatedStatCard from '../components/AnimatedStatCard';
import TrafficHeatmap from '../components/TrafficHeatmap';
import DonutChart from '../components/DonutChart';

dayjs.extend(relativeTime);

const { Text } = Typography;
const { useToken } = theme;

interface NetworkTabProps {
  clusterId?: number;
  analysisId?: number;
}

// Format bytes helper
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

const NetworkTab: React.FC<NetworkTabProps> = ({ clusterId, analysisId }) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  const [viewMode, setViewMode] = useState<string>('overview');
  
  // Theme-aware colors
  const cardBg = isDark ? '#1f1f1f' : '#fafbfc';
  const textPrimary = isDark ? 'rgba(255,255,255,0.85)' : '#2d3748';
  const textSecondary = isDark ? 'rgba(255,255,255,0.45)' : '#5a6978';
  const textMuted = isDark ? 'rgba(255,255,255,0.35)' : '#718096';
  
  // API Queries
  const { data: commStats, isLoading: statsLoading } = useGetCommunicationStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  const { data: communications, isLoading: commLoading } = useGetCommunicationsQuery(
    { cluster_id: clusterId, analysis_id: analysisId, limit: 100 },
    { skip: !clusterId }
  );

  const { data: crossNsComm, isLoading: crossNsLoading } = useGetCrossNamespaceCommunicationsQuery(
    { cluster_id: clusterId!, limit: 10 },
    { skip: !clusterId }
  );

  const { data: dnsData, isLoading: dnsLoading } = useGetDnsQueriesQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: 100 },
    { skip: !clusterId }
  );

  const { data: sniData, isLoading: sniLoading } = useGetSniEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: 50 },
    { skip: !clusterId }
  );

  const { data: networkFlows, isLoading: flowsLoading } = useGetNetworkFlowsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: 100 },
    { skip: !clusterId }
  );

  const { data: highRiskComms, isLoading: highRiskLoading } = useGetHighRiskCommunicationsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, risk_threshold: 0.3, limit: 20 },
    { skip: !clusterId }
  );

  // Error stats query - accurate categorized error counts
  const { data: errorStats, isLoading: errorStatsLoading } = useGetErrorStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  // Compute top talkers from communications
  const topTalkers = useMemo(() => {
    const comms = communications?.communications || [];
    const podTraffic = new Map<string, { name: string; namespace: string; bytes: number; requests: number }>();
    
    comms.forEach(comm => {
      // Source
      const srcKey = `${comm.source.namespace}/${comm.source.name}`;
      const srcExisting = podTraffic.get(srcKey);
      if (srcExisting) {
        srcExisting.bytes += comm.bytes_transferred;
        srcExisting.requests += comm.request_count;
      } else {
        podTraffic.set(srcKey, {
          name: comm.source.name,
          namespace: comm.source.namespace,
          bytes: comm.bytes_transferred,
          requests: comm.request_count
        });
      }
      
      // Destination
      const dstKey = `${comm.destination.namespace}/${comm.destination.name}`;
      const dstExisting = podTraffic.get(dstKey);
      if (dstExisting) {
        dstExisting.bytes += comm.bytes_transferred;
        dstExisting.requests += comm.request_count;
      } else {
        podTraffic.set(dstKey, {
          name: comm.destination.name,
          namespace: comm.destination.namespace,
          bytes: comm.bytes_transferred,
          requests: comm.request_count
        });
      }
    });
    
    return Array.from(podTraffic.values())
      .sort((a, b) => b.bytes - a.bytes)
      .slice(0, 8);
  }, [communications]);

  // Compute DNS stats
  const dnsStats = useMemo(() => {
    const queries = dnsData?.queries || [];
    const domainCounts = new Map<string, number>();
    
    queries.forEach(q => {
      const domain = q.query_name;
      domainCounts.set(domain, (domainCounts.get(domain) || 0) + 1);
    });
    
    return {
      total: dnsData?.total || 0,
      uniqueDomains: domainCounts.size,
      topDomains: Array.from(domainCounts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([domain, count]) => ({ domain, count }))
    };
  }, [dnsData]);

  // Compute TLS/SNI stats
  const tlsStats = useMemo(() => {
    const events = sniData?.events || [];
    const hostCounts = new Map<string, number>();
    
    events.forEach(e => {
      const host = e.server_name || e.sni_name || 'unknown';
      hostCounts.set(host, (hostCounts.get(host) || 0) + 1);
    });
    
    return {
      total: sniData?.total || 0,
      uniqueHosts: hostCounts.size,
      topHosts: Array.from(hostCounts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([host, count]) => ({ host, count }))
    };
  }, [sniData]);

  // Total traffic
  const totalTraffic = useMemo(() => {
    const flows = networkFlows?.events || [];
    let totalSent = 0;
    let totalRecv = 0;
    
    flows.forEach(f => {
      totalSent += f.bytes_sent || 0;
      totalRecv += f.bytes_received || 0;
    });
    
    return { sent: totalSent, received: totalRecv, total: totalSent + totalRecv };
  }, [networkFlows]);

  const isLoading = statsLoading || commLoading || dnsLoading || sniLoading || flowsLoading || highRiskLoading || errorStatsLoading;

  // Traffic heatmap data
  const trafficHeatmapData = useMemo(() => {
    const comms = communications?.communications || [];
    return comms.slice(0, 12).map(comm => ({
      source: comm.source.name,
      sourceNamespace: comm.source.namespace,
      destination: comm.destination.name,
      destinationNamespace: comm.destination.namespace,
      bytes: comm.bytes_transferred,
      requests: comm.request_count,
    }));
  }, [communications]);

  // Protocol donut data
  const protocolDonutData = useMemo(() => {
    if (!commStats?.protocol_distribution) return [];
    const colors: Record<string, string> = {
      TCP: '#0891b2',
      UDP: '#4caf50',
      HTTP: '#7c8eb5',
      HTTPS: '#22a6a6',
      gRPC: '#d4a844',
    };
    return Object.entries(commStats.protocol_distribution)
      .map(([protocol, count]) => ({
        label: protocol,
        value: count,
        color: colors[protocol] || '#8c8c8c',
      }));
  }, [commStats]);

  if (!clusterId) {
    return <Empty description="Select a cluster to view network data" />;
  }

  return (
    <div>
      {/* View Mode Selector */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          {/* Network Health Status Badge */}
          {errorStats && (
            <Tooltip
              title={
                <div style={{ minWidth: 200, fontFamily: 'inherit' }}>
                  <div style={{ 
                    fontWeight: 600, 
                    marginBottom: 8, 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    paddingBottom: 6,
                    borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`
                  }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }}>
                      {errorStats.health_status === 'healthy' || errorStats.health_status === 'good' ? (
                        <CheckCircleOutlined style={{ color: '#10b981' }} />
                      ) : errorStats.health_status === 'warning' ? (
                        <ExclamationCircleOutlined style={{ color: '#f59e0b' }} />
                      ) : (
                        <ExclamationCircleOutlined style={{ color: '#ef4444' }} />
                      )}
                      Network Health
                    </span>
                    <span style={{ 
                      fontSize: 10, 
                      padding: '2px 6px', 
                      borderRadius: 4,
                      fontWeight: 500,
                      background: errorStats.health_status === 'healthy' || errorStats.health_status === 'good' 
                        ? 'rgba(16, 185, 129, 0.15)' 
                        : errorStats.health_status === 'warning' 
                          ? 'rgba(245, 158, 11, 0.15)' 
                          : 'rgba(239, 68, 68, 0.15)',
                      color: errorStats.health_status === 'healthy' || errorStats.health_status === 'good' 
                        ? '#10b981' 
                        : errorStats.health_status === 'warning' 
                          ? '#f59e0b' 
                          : '#ef4444'
                    }}>
                      {(errorStats.health_status || 'healthy').charAt(0).toUpperCase() + (errorStats.health_status || 'healthy').slice(1)}
                    </span>
                  </div>
                  
                  {/* Critical/Warning split */}
                  <div style={{ display: 'flex', gap: 16, marginBottom: 8 }}>
                    <div>
                      <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2 }}>Critical</div>
                      <div style={{ fontSize: 16, fontWeight: 600, color: errorStats.total_critical > 0 ? '#ef4444' : '#10b981' }}>
                        {errorStats.total_critical.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2 }}>Warnings</div>
                      <div style={{ fontSize: 16, fontWeight: 600, color: errorStats.total_warnings > 0 ? '#f59e0b' : '#10b981' }}>
                        {errorStats.total_warnings.toLocaleString()}
                      </div>
                    </div>
                  </div>
                  
                  {/* Error breakdown */}
                  {errorStats.critical_by_type && Object.keys(errorStats.critical_by_type).length > 0 && (
                    <div style={{ fontSize: 11, marginBottom: 6, background: 'rgba(239, 68, 68, 0.08)', padding: '4px 6px', borderRadius: 4 }}>
                      <div style={{ color: '#ef4444', fontWeight: 500, marginBottom: 2 }}>Critical Errors</div>
                      {Object.entries(errorStats.critical_by_type).slice(0, 3).map(([type, count]) => (
                        <div key={type} style={{ display: 'flex', justifyContent: 'space-between', color: isDark ? 'rgba(239, 68, 68, 0.9)' : 'rgba(239, 68, 68, 0.85)' }}>
                          <span>{type.replace(/_/g, ' ')}</span>
                          <span>{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {errorStats.warnings_by_type && Object.keys(errorStats.warnings_by_type).length > 0 && (
                    <div style={{ fontSize: 11, background: 'rgba(245, 158, 11, 0.08)', padding: '4px 6px', borderRadius: 4 }}>
                      <div style={{ color: '#f59e0b', fontWeight: 500, marginBottom: 2 }}>Retransmits</div>
                      {Object.entries(errorStats.warnings_by_type).slice(0, 2).map(([type, count]) => (
                        <div key={type} style={{ display: 'flex', justifyContent: 'space-between', color: isDark ? 'rgba(245, 158, 11, 0.9)' : 'rgba(245, 158, 11, 0.85)' }}>
                          <span>{type.replace(/_/g, ' ')}</span>
                          <span>{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {errorStats.total_errors === 0 && (
                    <div style={{ color: '#10b981', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <CheckCircleOutlined /> No network errors detected
                    </div>
                  )}
                </div>
              }
              color={isDark ? token.colorBgElevated : '#fff'}
              overlayInnerStyle={{ 
                padding: 10,
                boxShadow: isDark ? '0 6px 16px rgba(0,0,0,0.4)' : '0 6px 16px rgba(0,0,0,0.08)',
                borderRadius: 8
              }}
            >
              <Tag 
                icon={errorStats.total_critical > 0 ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
                style={{ 
                  cursor: 'pointer',
                  background: errorStats.total_critical > 0 
                    ? 'rgba(239, 68, 68, 0.1)' 
                    : errorStats.total_warnings > 0 
                      ? 'rgba(245, 158, 11, 0.1)' 
                      : 'rgba(16, 185, 129, 0.1)',
                  color: errorStats.total_critical > 0 
                    ? '#ef4444' 
                    : errorStats.total_warnings > 0 
                      ? '#f59e0b' 
                      : '#10b981',
                  border: `1px solid ${errorStats.total_critical > 0 
                    ? 'rgba(239, 68, 68, 0.3)' 
                    : errorStats.total_warnings > 0 
                      ? 'rgba(245, 158, 11, 0.3)' 
                      : 'rgba(16, 185, 129, 0.3)'}`
                }}
              >
                {errorStats.total_critical > 0 
                  ? `${errorStats.total_critical} Critical` 
                  : errorStats.total_warnings > 0 
                    ? `${errorStats.total_warnings} Warnings`
                    : 'Healthy'}
                {errorStats.total_critical > 0 && errorStats.total_warnings > 0 && 
                  ` / ${errorStats.total_warnings} Warn`}
              </Tag>
            </Tooltip>
          )}
          {(highRiskComms?.length || 0) > 0 && (
            <Tag color="red" icon={<FireOutlined />}>
              {highRiskComms?.length} High Risk Connections
            </Tag>
          )}
        </Space>
        <Segmented
          value={viewMode}
          onChange={(value) => setViewMode(value as string)}
          options={[
            { label: 'Overview', value: 'overview', icon: <NodeIndexOutlined /> },
            { label: 'Heatmap', value: 'heatmap', icon: <HeatMapOutlined /> },
          ]}
          size="small"
        />
      </div>

      {/* Top Stats Row - Animated */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Total Connections"
            value={commStats?.total_communications || 0}
            icon={<ApiOutlined />}
            color="#2eb8b8"
            subtitle={`${commStats?.unique_namespaces || 0} namespaces`}
            loading={statsLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Traffic Volume"
            value={totalTraffic.total}
            icon={<SwapOutlined />}
            color="#3cc9c4"
            formatter={(v) => formatBytes(v)}
            subtitle={`↑ ${formatBytes(totalTraffic.sent)} ↓ ${formatBytes(totalTraffic.received)}`}
            loading={flowsLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="DNS Queries"
            value={dnsStats.total}
            icon={<GlobalOutlined />}
            color="#64b5f6"
            subtitle={`${dnsStats.uniqueDomains} unique domains`}
            loading={dnsLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="TLS/SNI Events"
            value={tlsStats.total}
            icon={<LockOutlined />}
            color="#e57373"
            subtitle={`${tlsStats.uniqueHosts} unique hosts`}
            loading={sniLoading}
          />
        </Col>
      </Row>

      {/* Conditional View: Heatmap or Overview */}
      {viewMode === 'heatmap' ? (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <TrafficHeatmap
              data={trafficHeatmapData}
              title="Network Traffic Heatmap"
              maxItems={12}
            />
          </Col>
        </Row>
      ) : (
        <>
          {/* Protocol Distribution & Top Talkers */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            {/* Protocol Distribution - Donut Chart */}
            <Col xs={24} lg={8}>
              <Card 
                title={
                  <Space>
                    <ThunderboltOutlined style={{ color: '#d4a844' }} />
                    <span>Protocol Distribution</span>
                  </Space>
                }
                bordered={false}
                style={{ height: '100%' }}
                extra={
                  <Tag color="orange" style={{ fontSize: 10 }}>
                    {Object.keys(commStats?.protocol_distribution || {}).length} protocols
                  </Tag>
                }
              >
                {statsLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : protocolDonutData.length > 0 ? (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                    <DonutChart
                      data={protocolDonutData}
                      size={180}
                      thickness={24}
                      centerValue={commStats?.total_communications || 0}
                      centerLabel="Connections"
                      animated={true}
                    />
                  </div>
                ) : (
                  <Empty description="No protocol data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>

        {/* Top Talkers - Enhanced */}
            <Col xs={24} lg={16}>
              <Card 
                title={
                  <Space>
                    <CloudServerOutlined style={{ color: '#0891b2' }} />
                    <span>Top Talkers</span>
                  </Space>
                }
                bordered={false}
                extra={
                  <Tag color="blue" style={{ fontSize: 10 }}>
                    {topTalkers.length} pods
                  </Tag>
                }
              >
                {commLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : topTalkers.length > 0 ? (
                  <Row gutter={[12, 12]}>
                    {topTalkers.map((pod, index) => {
                      const maxBytes = Math.max(...topTalkers.map(p => p.bytes));
                      const intensity = pod.bytes / maxBytes;
                      const colors = ['#e05252', '#c97a6d', '#d4a844', '#ffd666', '#4caf50', '#0891b2', '#7c8eb5', '#b37feb'];
                      const color = colors[index % colors.length];
                      
                      return (
                        <Col xs={12} sm={8} md={6} key={`${pod.namespace}-${pod.name}`}>
                          <Tooltip title={`${pod.name} - ${formatBytes(pod.bytes)} / ${pod.requests.toLocaleString()} requests`}>
                            <div style={{ 
                              background: `linear-gradient(135deg, ${color}15 0%, ${token.colorBgLayout} 100%)`,
                              borderRadius: 8,
                              padding: 12,
                              border: `1px solid ${color}30`,
                              position: 'relative',
                              overflow: 'hidden',
                              cursor: 'pointer',
                              transition: 'all 0.2s ease',
                            }}>
                              {/* Intensity bar */}
                              <div style={{
                                position: 'absolute',
                                bottom: 0,
                                left: 0,
                                right: 0,
                                height: 3,
                                background: `linear-gradient(90deg, ${color} ${intensity * 100}%, transparent ${intensity * 100}%)`,
                              }} />
                              
                              <Space direction="vertical" size={0} style={{ width: '100%' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                  <div style={{
                                    width: 20,
                                    height: 20,
                                    borderRadius: 4,
                                    background: color,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    color: token.colorTextLightSolid,
                                    fontSize: 10,
                                    fontWeight: 600,
                                  }}>
                                    {index + 1}
                                  </div>
                                </div>
                                <Text strong style={{ fontSize: 12, marginTop: 4 }} ellipsis>
                                  {pod.name}
                                </Text>
                                <Text type="secondary" style={{ fontSize: 10 }}>
                                  {pod.namespace}
                                </Text>
                                <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                  <Text style={{ fontSize: 16, fontWeight: 700, color }}>
                                    {formatBytes(pod.bytes)}
                                  </Text>
                                  <Text type="secondary" style={{ fontSize: 9 }}>
                                    {pod.requests >= 1000 ? `${(pod.requests/1000).toFixed(1)}K` : pod.requests} req
                                  </Text>
                                </div>
                              </Space>
                            </div>
                          </Tooltip>
                        </Col>
                      );
                    })}
                  </Row>
                ) : (
                  <Empty description="No traffic data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </Row>

      {/* Cross-Namespace & DNS/TLS */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            {/* Cross-Namespace Communications - Enhanced */}
            <Col xs={24} lg={12}>
              <Card 
                title={
                  <Space>
                    <LinkOutlined style={{ color: '#a67c9e' }} />
                    <span>Cross-Namespace Traffic</span>
                  </Space>
                }
                bordered={false}
                extra={
                  crossNsComm && crossNsComm.length > 0 && (
                    <Badge count={crossNsComm.length} style={{ backgroundColor: '#a67c9e' }} />
                  )
                }
              >
                {crossNsLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : crossNsComm && crossNsComm.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {crossNsComm.slice(0, 6).map((comm: any, index: number) => (
                      <div
                        key={index}
                        style={{
                          background: token.colorBgLayout,
                          borderRadius: 8,
                          padding: '10px 12px',
                          border: `1px solid ${token.colorBorderSecondary}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ textAlign: 'center' }}>
                              <Tag color="blue" style={{ fontSize: 9, margin: 0 }}>{comm.source.namespace}</Tag>
                              <br />
                              <Text strong style={{ fontSize: 11 }}>{comm.source.name}</Text>
                            </div>
                            
                            <div style={{ 
                              flex: 1, 
                              display: 'flex', 
                              alignItems: 'center', 
                              justifyContent: 'center',
                              position: 'relative',
                            }}>
                              <div style={{
                                height: 2,
                                flex: 1,
                                background: `linear-gradient(90deg, #0891b2 0%, #a67c9e 100%)`,
                                borderRadius: 1,
                              }} />
                              <ArrowUpOutlined style={{ 
                                color: '#a67c9e', 
                                transform: 'rotate(90deg)',
                                position: 'absolute',
                                right: -4,
                              }} />
                            </div>
                            
                            <div style={{ textAlign: 'center' }}>
                              <Tag color="purple" style={{ fontSize: 9, margin: 0 }}>{comm.destination.namespace}</Tag>
                              <br />
                              <Text strong style={{ fontSize: 11 }}>{comm.destination.name}</Text>
                            </div>
                          </div>
                        </div>
                        <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between' }}>
                          <Space size="middle">
                            <Text type="secondary" style={{ fontSize: 10 }}>
                              Port: <strong>{comm.port}</strong>
                            </Text>
                            <Text type="secondary" style={{ fontSize: 10 }}>
                              {comm.request_count.toLocaleString()} req
                            </Text>
                          </Space>
                          <Text style={{ fontSize: 11, fontWeight: 600, color: '#a67c9e' }}>
                            {formatBytes(comm.bytes_transferred)}
                          </Text>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty description="No cross-namespace traffic" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>

        {/* DNS & TLS Stats */}
        <Col xs={24} lg={12}>
          <Row gutter={[16, 16]}>
            {/* Top DNS Domains */}
            <Col span={24}>
              <Card 
                title={
                  <Space>
                    <GlobalOutlined style={{ color: '#4caf50' }} />
                    <span>Top DNS Domains</span>
                  </Space>
                }
                bordered={false}
                size="small"
              >
                {dnsLoading ? (
                  <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
                ) : dnsStats.topDomains.length > 0 ? (
                  <Space direction="vertical" style={{ width: '100%' }} size={4}>
                    {dnsStats.topDomains.map((item, idx) => (
                      <div key={item.domain} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Space>
                          <Text type="secondary" style={{ fontSize: 11, width: 16 }}>{idx + 1}.</Text>
                          <Tooltip title={item.domain}>
                            <Text style={{ fontSize: 11, maxWidth: 200 }} ellipsis>
                              {item.domain}
                            </Text>
                          </Tooltip>
                        </Space>
                        <Tag style={{ fontSize: 10 }}>{item.count}</Tag>
                      </div>
                    ))}
                  </Space>
                ) : (
                  <Empty description="No DNS data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>

            {/* Top TLS Hosts */}
            <Col span={24}>
              <Card 
                title={
                  <Space>
                    <LockOutlined style={{ color: '#22a6a6' }} />
                    <span>Top TLS Hosts</span>
                  </Space>
                }
                bordered={false}
                size="small"
              >
                {sniLoading ? (
                  <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
                ) : tlsStats.topHosts.length > 0 ? (
                  <Space direction="vertical" style={{ width: '100%' }} size={4}>
                    {tlsStats.topHosts.map((item, idx) => (
                      <div key={item.host} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Space>
                          <Text type="secondary" style={{ fontSize: 11, width: 16 }}>{idx + 1}.</Text>
                          <Tooltip title={item.host}>
                            <Text style={{ fontSize: 11, maxWidth: 200 }} ellipsis>
                              {item.host}
                            </Text>
                          </Tooltip>
                        </Space>
                        <Tag color="cyan" style={{ fontSize: 10 }}>{item.count}</Tag>
                      </div>
                    ))}
                  </Space>
                ) : (
                  <Empty description="No TLS data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
            </Row>
          </Col>
        </Row>
        </>
      )}
    </div>
  );
};

export default NetworkTab;

