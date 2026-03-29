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
  Badge,
  theme,
  Segmented
} from 'antd';
import { 
  AppstoreOutlined,
  ContainerOutlined,
  GlobalOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  BlockOutlined,
  HeatMapOutlined,
  PieChartOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useGetWorkloadsQuery, useGetNamespacesQuery, useGetWorkloadStatsQuery } from '../../../store/api/workloadApi';
import { useGetOomEventsQuery, useGetProcessEventsQuery } from '../../../store/api/eventsApi';
import { Workload, Namespace } from '../../../types';
import { useTheme } from '../../../contexts/ThemeContext';

// Import shared constants for consistent API limits
import { OOM_EVENTS_LIMIT } from '../../../utils/securityScore';

// Import custom components
import AnimatedStatCard from '../components/AnimatedStatCard';
import PodHealthGrid from '../components/PodHealthGrid';
import DonutChart from '../components/DonutChart';

dayjs.extend(relativeTime);

const { Text } = Typography;
const { useToken } = theme;

interface WorkloadTabProps {
  clusterId?: number;
  analysisId?: number;
}

// Workload type icons and colors
const workloadTypeConfig: Record<string, { icon: React.ReactNode; color: string }> = {
  pod: { icon: <ContainerOutlined />, color: '#0891b2' },
  deployment: { icon: <AppstoreOutlined />, color: '#4caf50' },
  service: { icon: <GlobalOutlined />, color: '#7c8eb5' },
  statefulset: { icon: <DatabaseOutlined />, color: '#d4a844' },
  daemonset: { icon: <CloudServerOutlined />, color: '#22a6a6' },
};

// Status colors
const statusColors: Record<string, string> = {
  Running: '#4caf50',
  Active: '#4caf50',
  Pending: '#c9a55a',
  Failed: '#e05252',
  Succeeded: '#0891b2',
  Unknown: '#8c8c8c',
  Terminating: '#d4a844',
};

const WorkloadTab: React.FC<WorkloadTabProps> = ({ clusterId, analysisId }) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  const [viewMode, setViewMode] = useState<string>('grid');
  
  // Theme-aware colors
  const cardBg = isDark ? '#1f1f1f' : '#fafbfc';
  const textPrimary = isDark ? 'rgba(255,255,255,0.85)' : '#2d3748';
  const textSecondary = isDark ? 'rgba(255,255,255,0.45)' : '#5a6978';
  const textMuted = isDark ? 'rgba(255,255,255,0.35)' : '#718096';
  
  // API Queries
  const { data: workloads = [], isLoading: workloadsLoading } = useGetWorkloadsQuery(
    { cluster_id: clusterId!, is_active: true },
    { skip: !clusterId }
  );

  const { data: namespaces = [], isLoading: namespacesLoading } = useGetNamespacesQuery(
    clusterId!,
    { skip: !clusterId }
  );

  const { data: workloadStats, isLoading: statsLoading, isError: statsError } = useGetWorkloadStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId || !analysisId }
  );

  const { data: oomData, isLoading: oomLoading } = useGetOomEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: OOM_EVENTS_LIMIT },
    { skip: !clusterId || !analysisId }
  );

  const { data: processData, isLoading: processLoading } = useGetProcessEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: OOM_EVENTS_LIMIT },
    { skip: !clusterId || !analysisId }
  );

  // Compute stats
  const computedStats = useMemo(() => {
    // Get type counts from workloadStats API (normalize to lowercase)
    const rawByType = workloadStats?.by_type || {};
    const byTypeFromStats: Record<string, number> = {};
    Object.entries(rawByType).forEach(([key, value]) => {
      byTypeFromStats[key.toLowerCase()] = (byTypeFromStats[key.toLowerCase()] || 0) + (value as number);
    });
    
    // Also calculate type counts from workloads array as fallback
    const byTypeFromWorkloads: Record<string, number> = {};
    workloads.forEach((w: Workload) => {
      const type = (w.workload_type || 'unknown').toLowerCase();
      byTypeFromWorkloads[type] = (byTypeFromWorkloads[type] || 0) + 1;
    });
    
    // Use workloadStats if available, otherwise use workloads array
    const byType = Object.keys(byTypeFromStats).length > 0 ? byTypeFromStats : byTypeFromWorkloads;
    
    const byNamespace = workloadStats?.by_namespace || {};
    
    // Status breakdown from workloads - normalize status keys
    const statusCounts: Record<string, number> = {};
    workloads.forEach((w: Workload) => {
      // Normalize status to capitalized form - default to Running for active workloads
      let rawStatus = w.status || 'Unknown';
      if (rawStatus === 'Unknown' || rawStatus === 'unknown' || !rawStatus) {
        rawStatus = w.is_active !== false ? 'Running' : 'Succeeded';
      }
      const status = rawStatus.charAt(0).toUpperCase() + rawStatus.slice(1).toLowerCase();
      statusCounts[status] = (statusCounts[status] || 0) + 1;
    });
    
    // Calculate running pods from either stats or workloads
    const runningFromStatus = statusCounts['Running'] || 0;
    
    return {
      total: workloadStats?.total_workloads || workloads.length,
      active: workloadStats?.active_workloads || workloads.filter((w: Workload) => 
        w.status === 'Running' || w.status === 'Active' || w.status === 'running' || w.status === 'active' || 
        (w.is_active !== false && (!w.status || w.status === 'Unknown' || w.status === 'unknown'))
      ).length,
      byType,
      byNamespace,
      statusCounts,
      namespaceCount: namespaces.length,
      runningPods: runningFromStatus,
    };
  }, [workloadStats, workloads, namespaces]);

  // OOM affected pods
  const oomAffectedPods = useMemo(() => {
    const events = oomData?.events || [];
    const podCounts = new Map<string, { pod: string; namespace: string; count: number; lastOom: string }>();
    
    events.forEach(e => {
      const key = `${e.namespace}/${e.pod}`;
      const existing = podCounts.get(key);
      if (existing) {
        existing.count++;
        if (e.timestamp > existing.lastOom) {
          existing.lastOom = e.timestamp;
        }
      } else {
        podCounts.set(key, {
          pod: e.pod,
          namespace: e.namespace,
          count: 1,
          lastOom: e.timestamp
        });
      }
    });
    
    return Array.from(podCounts.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  }, [oomData]);

  // Top namespaces by workload count - calculate from workloads if not provided by API
  const topNamespaces = useMemo(() => {
    // Calculate workload count per namespace from workloads array
    const workloadCountByNamespace: Record<string, number> = {};
    workloads.forEach((w: any) => {
      const ns = w.namespace_name || w.namespace || 'unknown';
      workloadCountByNamespace[ns] = (workloadCountByNamespace[ns] || 0) + 1;
    });
    
    // Map namespaces with calculated workload count
    return [...namespaces]
      .map((ns: Namespace) => ({
        ...ns,
        // Use API workload_count if provided, otherwise use calculated count
        workload_count: ns.workload_count || workloadCountByNamespace[ns.name] || 0
      }))
      .sort((a, b) => (b.workload_count || 0) - (a.workload_count || 0))
      .slice(0, 8);
  }, [namespaces, workloads]);

  // Recent workloads - handle both API field names (namespace vs namespace_name, updated_at vs last_seen)
  const recentWorkloads = useMemo(() => {
    return [...workloads]
      .map((w: any) => ({
        ...w,
        // Normalize field names: backend returns 'namespace', frontend expects 'namespace_name'
        namespace_name: w.namespace_name || w.namespace || 'unknown',
        // Normalize date fields: backend returns updated_at/created_at, frontend expects last_seen/first_seen
        last_seen: w.last_seen || w.updated_at || w.created_at,
        first_seen: w.first_seen || w.created_at,
        // Normalize status: if empty or null, mark as Running for active workloads
        status: w.status && w.status !== 'unknown' ? w.status : (w.is_active !== false ? 'Running' : 'Unknown'),
      }))
      .sort((a: any, b: any) => 
        new Date(b.last_seen || b.first_seen).getTime() - new Date(a.last_seen || a.first_seen).getTime()
      )
      .slice(0, 10);
  }, [workloads]);

  const isLoading = workloadsLoading || namespacesLoading || (statsLoading && !statsError);

  // Pod health data for grid - default to Running for active workloads
  const podHealthData = useMemo(() => {
    return workloads.slice(0, 100).map((w: any) => {
      // Map status - if unknown or empty, assume Running for active workloads
      let status = w.status || 'Running';
      if (status === 'Unknown' || status === 'unknown' || !status) {
        status = w.is_active !== false ? 'Running' : 'Succeeded';
      }
      // Handle both API field names
      const namespace = w.namespace_name || w.namespace || 'default';
      const firstSeen = w.first_seen || w.created_at;
      
      return {
        name: w.name || 'unknown',
        namespace: namespace,
        status: status as any,
        restarts: 0,
        age: firstSeen ? dayjs(firstSeen).fromNow() : undefined,
        oomKilled: oomAffectedPods.some(p => p.pod === w.name),
        workload_type: w.workload_type,
      };
    });
  }, [workloads, oomAffectedPods]);

  // Workload type donut data
  const workloadTypeDonutData = useMemo(() => {
    if (!computedStats.byType) return [];
    const colors: Record<string, string> = {
      pod: '#0891b2',
      deployment: '#4caf50',
      service: '#7c8eb5',
      statefulset: '#d4a844',
      daemonset: '#22a6a6',
    };
    return Object.entries(computedStats.byType)
      .map(([type, count]) => ({
        label: type.charAt(0).toUpperCase() + type.slice(1),
        value: count as number,
        color: colors[type] || '#8c8c8c',
      }));
  }, [computedStats.byType]);

  // Status donut data
  const statusDonutData = useMemo(() => {
    if (!computedStats.statusCounts) return [];
    return Object.entries(computedStats.statusCounts)
      .map(([status, count]) => ({
        label: status,
        value: count,
        color: statusColors[status] || '#8c8c8c',
      }));
  }, [computedStats.statusCounts]);

  if (!clusterId) {
    return <Empty description="Select a cluster to view workload data" />;
  }

  return (
    <div>
      {/* View Mode Selector */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          {oomAffectedPods.length > 0 && (
            <Tag color="red" icon={<ExclamationCircleOutlined />}>
              {oomAffectedPods.length} Pods with OOM
            </Tag>
          )}
        </Space>
        <Segmented
          value={viewMode}
          onChange={(value) => setViewMode(value as string)}
          options={[
            { label: 'Grid View', value: 'grid', icon: <BlockOutlined /> },
            { label: 'Charts', value: 'charts', icon: <PieChartOutlined /> },
          ]}
          size="small"
        />
      </div>

      {/* Top Stats Row - Animated */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Total Workloads"
            value={computedStats.total}
            icon={<AppstoreOutlined />}
            color="#2eb8b8"
            subtitle={`${computedStats.active} active`}
            loading={isLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Namespaces"
            value={computedStats.namespaceCount}
            icon={<GlobalOutlined />}
            color="#3cc9c4"
            subtitle="In analysis"
            loading={namespacesLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Active Workloads"
            value={computedStats.active}
            icon={<ContainerOutlined />}
            color="#64b5f6"
            subtitle="Currently running"
            loading={isLoading}
          />
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="OOM Events"
            value={oomData?.total || 0}
            icon={<ExclamationCircleOutlined />}
            color={(oomData?.total || 0) > 0 ? "#e57373" : "#8fa8b8"}
            subtitle={`${oomAffectedPods.length} pods affected`}
            loading={oomLoading}
            pulseEffect={(oomData?.total || 0) > 0}
          />
        </Col>
      </Row>

      {/* Conditional View: Grid or Charts */}
      {viewMode === 'grid' ? (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <PodHealthGrid
              pods={podHealthData}
              title="Workload Health Grid"
              maxPods={100}
            />
          </Col>
        </Row>
      ) : (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {/* Workload Types Donut */}
          <Col xs={24} lg={8}>
            <Card 
              title={
                <Space>
                  <AppstoreOutlined style={{ color: '#0891b2' }} />
                  <span>Workload Types</span>
                </Space>
              }
              bordered={false}
            >
              {isLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
              ) : workloadTypeDonutData.length > 0 ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                  <DonutChart
                    data={workloadTypeDonutData}
                    size={180}
                    thickness={24}
                    centerValue={computedStats.total}
                    centerLabel="Total"
                    animated={true}
                  />
                </div>
              ) : (
                <Empty description="No workloads" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Col>

          {/* Status Distribution Donut */}
          <Col xs={24} lg={8}>
            <Card 
              title={
                <Space>
                  <SyncOutlined style={{ color: '#4caf50' }} />
                  <span>Status Distribution</span>
                </Space>
              }
              bordered={false}
            >
              {isLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
              ) : statusDonutData.length > 0 ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                  <DonutChart
                    data={statusDonutData}
                    size={180}
                    thickness={24}
                    centerValue={computedStats.active}
                    centerLabel="Active"
                    animated={true}
                  />
                </div>
              ) : (
                <Empty description="No status data" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Col>

          {/* OOM Affected Pods - Enhanced */}
          <Col xs={24} lg={8}>
            <Card 
              title={
                <Space>
                  <ExclamationCircleOutlined style={{ color: '#e05252' }} />
                  <span>OOM Affected Pods</span>
                </Space>
              }
              bordered={false}
              extra={
                oomAffectedPods.length > 0 && (
                  <Badge count={oomAffectedPods.length} style={{ backgroundColor: '#e05252' }} />
                )
              }
            >
              {oomLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
              ) : oomAffectedPods.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {oomAffectedPods.map((item, index) => (
                    <div
                      key={`${item.namespace}-${item.pod}`}
                      style={{
                        padding: '10px 12px',
                        background: `linear-gradient(90deg, #e0525210 0%, ${token.colorBgLayout} 100%)`,
                        borderRadius: 8,
                        borderLeft: '3px solid #e05252',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong style={{ fontSize: 12 }}>{item.pod}</Text>
                          <br />
                          <Tag style={{ fontSize: 10, marginTop: 4 }}>{item.namespace}</Tag>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <Badge count={item.count} style={{ backgroundColor: '#e05252' }} />
                          <br />
                          <Text type="secondary" style={{ fontSize: 10, color: textMuted }}>
                            {dayjs(item.lastOom).format('MM-DD HH:mm')}
                          </Text>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty 
                  description="No OOM events" 
                  image={<CheckCircleOutlined style={{ fontSize: 48, color: '#4caf50' }} />}
                />
              )}
            </Card>
          </Col>
        </Row>
      )}

      {/* Namespaces & Recent Workloads */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Top Namespaces */}
        <Col xs={24} lg={12}>
          <Card 
            title={
              <Space>
                <GlobalOutlined style={{ color: '#7c8eb5' }} />
                <span>Top Namespaces</span>
              </Space>
            }
            bordered={false}
          >
            {namespacesLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : topNamespaces.length > 0 ? (
              <Row gutter={[12, 12]}>
                {topNamespaces.map((ns: Namespace, index: number) => (
                  <Col xs={12} sm={8} md={6} key={ns.id}>
                    <Card size="small" style={{ background: token.colorBgLayout, textAlign: 'center' }}>
                      <Tag color="purple" style={{ marginBottom: 4 }}>#{index + 1}</Tag>
                      <br />
                      <Tooltip title={ns.name}>
                        <Text strong style={{ fontSize: 12 }} ellipsis>
                          {ns.name}
                        </Text>
                      </Tooltip>
                      <br />
                      <Text style={{ fontSize: 18, fontWeight: 600, color: '#7c8eb5' }}>
                        {ns.workload_count || 0}
                      </Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 10 }}>workloads</Text>
                    </Card>
                  </Col>
                ))}
              </Row>
            ) : (
              <Empty description="No namespaces" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Recent Workloads */}
        <Col xs={24} lg={12}>
          <Card 
            title={
              <Space>
                <ClockCircleOutlined style={{ color: '#0891b2' }} />
                <span>Recent Workloads</span>
              </Space>
            }
            bordered={false}
          >
            {workloadsLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : recentWorkloads.length > 0 ? (
              <Table
                dataSource={recentWorkloads}
                pagination={false}
                size="small"
                columns={[
                  {
                    title: 'Name',
                    dataIndex: 'name',
                    key: 'name',
                    render: (name: string, record: Workload) => {
                      const config = workloadTypeConfig[record.workload_type] || { icon: <AppstoreOutlined />, color: '#8c8c8c' };
                      return (
                        <Space>
                          <span style={{ color: config.color }}>{config.icon}</span>
                          <Text strong style={{ fontSize: 12 }}>{name}</Text>
                        </Space>
                      );
                    },
                  },
                  {
                    title: 'Namespace',
                    dataIndex: 'namespace_name',
                    key: 'namespace',
                    render: (ns: string) => <Tag style={{ fontSize: 10 }}>{ns}</Tag>,
                  },
                  {
                    title: 'Status',
                    dataIndex: 'status',
                    key: 'status',
                    render: (status: string) => (
                      <Tag color={statusColors[status] || 'default'} style={{ fontSize: 10 }}>
                        {status}
                      </Tag>
                    ),
                  },
                  {
                    title: 'Last Seen',
                    dataIndex: 'last_seen',
                    key: 'last_seen',
                    render: (date: string) => (
                      <Text type="secondary" style={{ fontSize: 10 }}>
                        {dayjs(date).format('MM-DD HH:mm')}
                      </Text>
                    ),
                  },
                ]}
              />
            ) : (
              <Empty description="No workloads" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default WorkloadTab;

